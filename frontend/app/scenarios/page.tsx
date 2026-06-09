"use client";
import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Globe, TrendingUp, AlertTriangle, DollarSign, Loader2, ChevronDown, ChevronUp, RefreshCw, X } from "lucide-react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import { useAnalysisReady } from "@/lib/analysis-ready-context";
import { useAiTask } from "@/contexts/AiTaskContext";
import { useSSE } from "@/hooks/useSSE";
import { MarkdownLite } from "@/components/ui/MarkdownLite";
import { SupplyPowerFlow } from "@/components/SupplyPowerFlow";
import { SectorTrend } from "@/components/SectorTrend";
import { AiCostBadge } from "@/components/ui/AiCostBadge";
import { useAuth, getToken } from "@/lib/auth-context";
import { useIsMobile } from "@/lib/use-is-mobile";

// Next.js 프록시 우회 — 프록시가 큰 done JSON을 버퍼링해서 결과가 안 뜨는 문제 방지
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// 시나리오 상세분석은 글로벌 AI 태스크 시스템(useSSE+globalId)으로 실행 →
// 페이지 이동해도 백그라운드 유지 + 완료 시 상단 벨 알림 + 새로고침 복원(컨텍스트가 자체 보관).

// ── 타입 정의 ──────────────────────────────────────────────────────────────────
interface StockEntry {
  name: string;
  ticker: string;
  reason: string;
  valuation_note?: string;
  signal: string;
  signal_reason: string;
  buy_target?: string;
  sell_target?: string;
  stop_loss?: string;
}

interface ThemeStock {
  name: string;
  ticker: string;
  horizon?: string;   // "단타" | "중장기"
  type: string;
  historical_pattern: string;
  reason: string;
  signal?: string;
  signal_reason?: string;
}

interface Scenario {
  label: string;
  title: string;
  probability_pct: number;
  market_direction: string;
  trigger: string;
  economic_analysis: string;
  rising_stocks: StockEntry[];
  falling_stocks: StockEntry[];
  theme_stocks: ThemeStock[];
  short_strategy: string;
  long_strategy: string;
}

interface Issue {
  issue_no?: number;
  title: string;
  summary: string;
  urgency?: string;
  category?: string;
  scenarios: Scenario[];
}

interface DetailResult {
  deep_analysis: string;
  historical_precedent: string;
  key_risks: string[];
  short_detail: {
    entry: string;
    exit: string;
    timing: string;
    stocks: Array<{ name: string; ticker: string; entry_point: string; target: string; stop: string; note: string }>;
  };
  long_detail: {
    thesis: string;
    hold_period: string;
    position_sizing: string;
    stocks: Array<{ name: string; ticker: string; reason: string; catalyst: string }>;
  };
}

// ── 헬퍼 함수 ─────────────────────────────────────────────────────────────────
function isKrTicker(ticker: string) {
  return /^\d{6}$/.test(ticker);
}

function signalColor(signal: string): string {
  if (signal === "매우 강력 추천") return "#00c853";
  if (signal === "추천")           return "#69f0ae";
  if (signal === "중간추천")       return "#ffd740";
  if (signal === "비추천")         return "#ff7043";
  if (signal === "매우 비추천")    return "#f44336";
  return "var(--color-muted)";
}

async function readSSE(
  url: string,
  method: "GET" | "POST" = "GET",
  body?: object,
  onMessage?: (msg: string) => void,
  signal?: AbortSignal
): Promise<any> {
  const token = getToken();
  const opts: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
      "ngrok-skip-browser-warning": "69420",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal,
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE_URL}${url}`, opts);
  // 에러 상태(특히 403 크레딧 부족)는 SSE 본문이 아니므로 먼저 처리.
  // 안 하면 아래 SSE 파서가 빈 결과(null)를 돌려주고, 호출부가 그 빈 값을 저장해 버린다.
  if (!res.ok) {
    let detail = "";
    try { detail = await res.text(); } catch {}
    if (res.status === 403 && detail.includes("NEED_AI_CREDIT")) {
      throw new Error("NEED_AI_CREDIT");
    }
    throw new Error(detail || `요청 실패 (${res.status})`);
  }
  if (!res.body) throw new Error("No SSE body");
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      try {
        const d = JSON.parse(line.slice(5).trim());
        if (d.status === "running" && onMessage) onMessage(d.message ?? "분석 중...");
        if (d.status === "done") return d.result;
        if (d.status === "error") throw new Error(d.message ?? "SSE 오류");
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }
  return null;
}

// 시나리오 에러 메시지를 사용자용으로 정리 (Error: 접두/내부 코드 제거)
function isCreditError(msg: string): boolean {
  return !!msg && msg.includes("NEED_AI_CREDIT");
}
function cleanScenarioError(msg: string): string {
  if (!msg) return "";
  if (isCreditError(msg)) {
    return "AI 사용 횟수가 없어 새로 생성할 수 없습니다. 관리자 승인(크레딧)이 필요합니다.";
  }
  return msg.replace(/^Error:\s*/, "");
}

// ── 시그널 뱃지 ────────────────────────────────────────────────────────────────
function SignalBadge({ signal }: { signal: string }) {
  return (
    <span style={{
      display: "inline-block",
      padding: "1px 7px",
      borderRadius: "10px",
      fontSize: "0.7rem",
      fontWeight: 700,
      background: `${signalColor(signal)}22`,
      border: `1px solid ${signalColor(signal)}`,
      color: signalColor(signal),
      flexShrink: 0,
    }}>
      {signal}
    </span>
  );
}

// ── 시장 뱃지 ─────────────────────────────────────────────────────────────────
function MarketBadge({ ticker }: { ticker: string }) {
  const kr = isKrTicker(ticker);
  return (
    <span style={{
      display: "inline-block",
      padding: "1px 6px",
      borderRadius: "4px",
      fontSize: "0.68rem",
      fontWeight: 700,
      background: kr ? "rgba(0,120,255,0.15)" : "rgba(50,200,100,0.15)",
      border: kr ? "1px solid rgba(0,120,255,0.4)" : "1px solid rgba(50,200,100,0.4)",
      color: kr ? "#60a5fa" : "var(--color-success)",
    }}>
      {kr ? "🇰🇷 KR" : "🇺🇸 US"}
    </span>
  );
}

// ── 종목 카드 행 (상승/하락) ───────────────────────────────────────────────────
type PriceEntry = { price: number; change_pct: number };

function StockRow({ stock, priceEntry, onClick }: {
  stock: StockEntry;
  priceEntry?: PriceEntry | null;
  onClick: () => void;
}) {
  const isKr = isKrTicker(stock.ticker);
  const up   = (priceEntry?.change_pct ?? 0) >= 0;
  const hasTargets = stock.buy_target || stock.sell_target || stock.stop_loss;

  return (
    <div
      onClick={onClick}
      style={{
        display: "flex", flexDirection: "column", gap: "5px",
        padding: "10px 12px",
        background: "rgba(0,0,0,0.2)",
        borderRadius: "6px",
        border: "1px solid var(--color-border)",
        cursor: "pointer",
        transition: "border-color 0.15s",
      }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--color-accent)")}
      onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--color-border)")}
    >
      {/* 종목명 + 배지 + 현재가 */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "6px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "5px", flexWrap: "wrap", flex: 1 }}>
          <span style={{ fontWeight: 700, fontSize: "0.88rem" }}>{stock.name}</span>
          <span style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>({stock.ticker})</span>
          <MarketBadge ticker={stock.ticker} />
          {stock.signal && <SignalBadge signal={stock.signal} />}
        </div>
        {/* 현재가 */}
        {priceEntry && priceEntry.price > 0 && (
          <div style={{ textAlign: "right", flexShrink: 0, minWidth: "70px" }}>
            <div style={{ fontWeight: 700, fontSize: "0.8rem", color: "var(--color-text)" }}>
              {isKr ? `₩${priceEntry.price.toLocaleString()}` : `$${priceEntry.price.toFixed(2)}`}
            </div>
            <div style={{ fontSize: "0.72rem", fontWeight: 700, color: up ? "var(--color-danger)" : "var(--color-primary)" }}>
              {up ? "▲" : "▼"} {Math.abs(priceEntry.change_pct).toFixed(2)}%
            </div>
          </div>
        )}
      </div>

      {stock.signal_reason && (
        <div style={{ fontSize: "0.76rem", color: "var(--color-text)", fontWeight: 600 }}>{stock.signal_reason}</div>
      )}
      <div style={{ fontSize: "0.74rem", color: "var(--color-muted)", lineHeight: 1.4 }}>{stock.reason}</div>
      {stock.valuation_note && (
        <div style={{ fontSize: "0.71rem", color: "var(--color-muted)", fontStyle: "italic" }}>{stock.valuation_note}</div>
      )}

      {/* 매수타점 / 목표가 / 손절선 */}
      {hasTargets && (
        <div style={{
          display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "2px",
          background: "rgba(0,0,0,0.25)", borderRadius: "5px", padding: "6px 8px",
          fontSize: "0.72rem",
        }}
          onClick={e => e.stopPropagation()}
        >
          {stock.buy_target && (
            <span>💰 매수 <strong style={{ color: "#69f0ae" }}>{stock.buy_target}</strong></span>
          )}
          {stock.sell_target && (
            <span>🎯 목표 <strong style={{ color: "#ff6b6b" }}>{stock.sell_target}</strong></span>
          )}
          {stock.stop_loss && (
            <span>🛡️ 손절 <strong style={{ color: "#60a5fa" }}>{stock.stop_loss}</strong></span>
          )}
        </div>
      )}
    </div>
  );
}

// ── 테마주 카드 ───────────────────────────────────────────────────────────────
function ThemeStockRow({ stock, priceEntry, onClick }: {
  stock: ThemeStock;
  priceEntry?: PriceEntry | null;
  onClick: () => void;
}) {
  const isKr = isKrTicker(stock.ticker);
  const up   = (priceEntry?.change_pct ?? 0) >= 0;

  return (
    <div
      onClick={onClick}
      style={{
        display: "flex", flexDirection: "column", gap: "5px",
        padding: "10px 12px",
        background: "rgba(0,0,0,0.2)",
        borderRadius: "6px",
        border: "1px solid var(--color-border)",
        cursor: "pointer",
        transition: "border-color 0.15s",
      }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--color-accent)")}
      onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--color-border)")}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "6px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "5px", flexWrap: "wrap", flex: 1 }}>
          <span style={{ fontWeight: 700, fontSize: "0.88rem" }}>{stock.name}</span>
          <span style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>({stock.ticker})</span>
          <MarketBadge ticker={stock.ticker} />
          {stock.horizon && (
            <span style={{
              display: "inline-block", padding: "1px 7px", borderRadius: "10px", fontSize: "0.7rem", fontWeight: 800,
              background: stock.horizon === "중장기" ? "rgba(80,160,255,0.18)" : "rgba(255,140,50,0.18)",
              border: stock.horizon === "중장기" ? "1px solid #5aa0ff" : "1px solid #ff8c32",
              color: stock.horizon === "중장기" ? "#5aa0ff" : "#ff8c32",
            }}>
              {stock.horizon === "중장기" ? "📆 중장기" : "⚡ 단타"}
            </span>
          )}
          <span style={{
            display: "inline-block", padding: "1px 7px", borderRadius: "10px", fontSize: "0.7rem", fontWeight: 700,
            background: stock.type === "직접관련주" ? "rgba(255,180,50,0.15)" : "rgba(180,100,255,0.15)",
            border: stock.type === "직접관련주" ? "1px solid var(--color-warning)" : "1px solid rgba(180,100,255,0.6)",
            color: stock.type === "직접관련주" ? "var(--color-warning)" : "#c084fc",
          }}>
            {stock.type}
          </span>
          {stock.signal && <SignalBadge signal={stock.signal} />}
        </div>
        {priceEntry && priceEntry.price > 0 && (
          <div style={{ textAlign: "right", flexShrink: 0, minWidth: "70px" }}>
            <div style={{ fontWeight: 700, fontSize: "0.8rem", color: "var(--color-text)" }}>
              {isKr ? `₩${priceEntry.price.toLocaleString()}` : `$${priceEntry.price.toFixed(2)}`}
            </div>
            <div style={{ fontSize: "0.72rem", fontWeight: 700, color: up ? "var(--color-danger)" : "var(--color-primary)" }}>
              {up ? "▲" : "▼"} {Math.abs(priceEntry.change_pct).toFixed(2)}%
            </div>
          </div>
        )}
      </div>
      {stock.signal_reason && (
        <div style={{ fontSize: "0.74rem", color: "var(--color-text)", fontWeight: 600 }}>{stock.signal_reason}</div>
      )}
      {stock.historical_pattern && (
        <div style={{ fontSize: "0.74rem", color: "var(--color-accent)", fontWeight: 600 }}>
          과거 패턴: {stock.historical_pattern}
        </div>
      )}
      <div style={{ fontSize: "0.74rem", color: "var(--color-muted)", lineHeight: 1.4 }}>{stock.reason}</div>
    </div>
  );
}

// ── 섹션 헤더 ─────────────────────────────────────────────────────────────────
function SectionHeader({ title, count }: { title: string; count?: number }) {
  return (
    <div style={{
      fontSize: "0.82rem", fontWeight: 800, color: "var(--color-muted)",
      padding: "6px 0 4px",
      borderBottom: "1px solid var(--color-border)",
      marginBottom: "8px",
      display: "flex", alignItems: "center", gap: "6px",
    }}>
      {title}
      {count !== undefined && (
        <span style={{ fontWeight: 600, color: "var(--color-muted)", fontSize: "0.75rem" }}>({count})</span>
      )}
    </div>
  );
}

// ── 전략 박스 ─────────────────────────────────────────────────────────────────
function StrategyBox({ label, text, color }: { label: string; text: string; color: string }) {
  return (
    <div style={{
      background: `${color}0d`,
      border: `1px solid ${color}44`,
      borderRadius: "6px",
      padding: "10px 12px",
      flex: 1,
    }}>
      <div style={{ fontSize: "0.75rem", fontWeight: 800, color, marginBottom: "6px" }}>{label}</div>
      <div style={{ fontSize: "0.82rem", color: "var(--color-text)", lineHeight: 1.5 }}>{text}</div>
    </div>
  );
}

// ── 상세 분석 패널 ────────────────────────────────────────────────────────────
function DetailPanel({ detail }: { detail: DetailResult }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* deep_analysis */}
      <div>
        <SectionHeader title="심층 분석" />
        <MarkdownLite text={detail.deep_analysis} style={{ fontSize: "0.85rem", color: "var(--color-text)", lineHeight: 1.7 }} />
      </div>

      {/* historical_precedent */}
      {detail.historical_precedent && (
        <div>
          <SectionHeader title="역사적 선례" />
          <div style={{ fontSize: "0.85rem", color: "var(--color-muted)", lineHeight: 1.6, fontStyle: "italic" }}>
            {detail.historical_precedent}
          </div>
        </div>
      )}

      {/* key_risks */}
      {detail.key_risks?.length > 0 && (
        <div>
          <SectionHeader title="핵심 리스크" count={detail.key_risks.length} />
          <ul style={{ margin: 0, padding: "0 0 0 1.2rem" }}>
            {detail.key_risks.map((r, i) => (
              <li key={i} style={{ fontSize: "0.82rem", color: "var(--color-text)", lineHeight: 1.6, marginBottom: "2px" }}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {/* short_detail */}
      {detail.short_detail && (
        <div>
          <SectionHeader title="단타 상세 전략" />
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "10px" }}>
            {[
              { l: "진입", v: detail.short_detail.entry },
              { l: "청산", v: detail.short_detail.exit },
              { l: "타이밍", v: detail.short_detail.timing },
            ].map(({ l, v }) => v ? (
              <div key={l} style={{ background: "rgba(0,0,0,0.2)", border: "1px solid var(--color-border)", borderRadius: "6px", padding: "8px 12px", fontSize: "0.8rem" }}>
                <span style={{ color: "var(--color-muted)", fontWeight: 700 }}>{l}: </span>
                <span style={{ color: "var(--color-text)" }}>{v}</span>
              </div>
            ) : null)}
          </div>
          {detail.short_detail.stocks?.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--color-border)", color: "var(--color-muted)" }}>
                    {["종목", "티커", "진입점", "목표가", "손절가", "메모"].map(h => (
                      <th key={h} style={{ padding: "6px 8px", textAlign: "left", fontWeight: 700 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {detail.short_detail.stocks.map((s, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                      <td style={{ padding: "6px 8px", fontWeight: 600 }}>{s.name}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-muted)" }}>{s.ticker}</td>
                      <td style={{ padding: "6px 8px" }}>{s.entry_point}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-success)" }}>{s.target}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-danger)" }}>{s.stop}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-muted)", fontSize: "0.75rem" }}>{s.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* long_detail */}
      {detail.long_detail && (
        <div>
          <SectionHeader title="장타 상세 전략" />
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "10px" }}>
            {[
              { l: "투자 논지", v: detail.long_detail.thesis },
              { l: "보유 기간", v: detail.long_detail.hold_period },
              { l: "포지션 사이징", v: detail.long_detail.position_sizing },
            ].map(({ l, v }) => v ? (
              <div key={l} style={{ background: "rgba(0,0,0,0.2)", border: "1px solid var(--color-border)", borderRadius: "6px", padding: "8px 12px", fontSize: "0.8rem", flex: 1, minWidth: "140px" }}>
                <span style={{ color: "var(--color-muted)", fontWeight: 700 }}>{l}: </span>
                <span style={{ color: "var(--color-text)" }}>{v}</span>
              </div>
            ) : null)}
          </div>
          {detail.long_detail.stocks?.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--color-border)", color: "var(--color-muted)" }}>
                    {["종목", "티커", "분할매수 타점", "장기 목표가 (+30%)", "손절가 (-15%)", "보유 기간", "촉매 및 투자 근거"].map(h => (
                      <th key={h} style={{ padding: "6px 8px", textAlign: "left", fontWeight: 700 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {detail.long_detail.stocks.map((s: any, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                      <td style={{ padding: "6px 8px", fontWeight: 600 }}>{s.name}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-muted)" }}>{s.ticker}</td>
                      <td style={{ padding: "6px 8px", color: "#69f0ae" }}>{s.entry_point || "-"}</td>
                      <td style={{ padding: "6px 8px", color: "#ff6b6b" }}>{s.target || "-"}</td>
                      <td style={{ padding: "6px 8px", color: "#60a5fa" }}>{s.stop || "-"}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-text)", fontWeight: 600 }}>{s.hold_period || "-"}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-muted)", fontSize: "0.75rem" }}>
                        {s.catalyst && <strong style={{ color: "var(--color-accent)" }}>[촉매: {s.catalyst}] </strong>}
                        {s.reason || ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── 시나리오 콘텐츠 ────────────────────────────────────────────────────────────
function ScenarioContent({ scenario, issueTitle }: { scenario: Scenario; issueTitle: string }) {
  const router = useRouter();
  const [showDetail, setShowDetail] = useState(false);
  const [detailPending, setDetailPending] = useState(false);   // 5초 취소 유예 중 (아직 AI 호출 전)
  const [detailCountdown, setDetailCountdown] = useState(0);
  const detailGraceTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // 상세분석을 글로벌 태스크로 실행 → 다른 화면 이동해도 유지 + 완료 시 상단 벨 알림 + 새로고침 복원
  const _detailId = `scenario-detail-${issueTitle}::${scenario.title}`.replace(/\s+/g, " ").trim().slice(0, 120);
  const detailTask = useSSE<DetailResult>("/api/ai/scenarios/detail", {
    method: "POST",
    globalId: _detailId,
    globalTitle: `${scenario.title} 상세분석`,
  });
  const detailStatus = detailTask.status;   // idle | running | done | error
  const detailResult = detailTask.result;
  const detailMsg = detailTask.message;

  // unmount 시 유예 타이머 정리
  useEffect(() => () => { if (detailGraceTimer.current) clearInterval(detailGraceTimer.current); }, []);

  const krRising   = scenario.rising_stocks?.filter(s => isKrTicker(s.ticker))  ?? [];
  const usRising   = scenario.rising_stocks?.filter(s => !isKrTicker(s.ticker)) ?? [];
  const krFalling  = scenario.falling_stocks?.filter(s => isKrTicker(s.ticker)) ?? [];
  const usFalling  = scenario.falling_stocks?.filter(s => !isKrTicker(s.ticker))?? [];
  const themeStocks = scenario.theme_stocks ?? [];

  // ── 실시간 현재가 조회 ─────────────────────────────────────────────────────
  const allStocks = useMemo(() => [
    ...(scenario.rising_stocks ?? []),
    ...(scenario.falling_stocks ?? []),
    ...(scenario.theme_stocks ?? []),
  ], [scenario]);

  const krTickers = useMemo(() =>
    [...new Set(allStocks.map(s => s.ticker).filter(t => isKrTicker(t)))],
    [allStocks]
  );
  const usTickers = useMemo(() =>
    [...new Set(allStocks.map(s => s.ticker).filter(t => !isKrTicker(t)))],
    [allStocks]
  );

  const { data: krPrices } = useSWR(
    krTickers.length > 0 ? `sc-kr-prices-${krTickers.join(",")}` : null,
    async () => {
      const map: Record<string, PriceEntry> = {};
      await Promise.all(krTickers.map(async (code) => {
        try {
          const d = await api.kr.stockPrice(code) as any;
          if (d?.price) map[code] = { price: d.price, change_pct: d.change_pct ?? 0 };
        } catch {}
      }));
      return map;
    },
    { revalidateOnFocus: false }
  );

  const { data: usPrices } = useSWR(
    usTickers.length > 0 ? `sc-us-prices-${usTickers.join(",")}` : null,
    async () => {
      const arr = await api.us.stocks(usTickers) as any[];
      const map: Record<string, PriceEntry> = {};
      for (const s of (arr ?? [])) {
        const ticker = s["심볼"] ?? s.ticker ?? "";
        if (ticker) map[ticker] = { price: s["현재가($)"] ?? 0, change_pct: s["등락률(%)"] ?? 0 };
      }
      return map;
    },
    { revalidateOnFocus: false }
  );

  const priceMap: Record<string, PriceEntry> = { ...(krPrices ?? {}), ...(usPrices ?? {}) };

  // 상세분석 클릭 → 5초 취소 유예 후 AI 호출 시작. 유예 중 취소하면 호출 안 함 = 토큰 0.
  const startDetailWithGrace = () => {
    setShowDetail(true);
    if (detailStatus === "running" || detailPending) return;
    setDetailPending(true);
    setDetailCountdown(5);
    if (detailGraceTimer.current) clearInterval(detailGraceTimer.current);
    detailGraceTimer.current = setInterval(() => {
      setDetailCountdown((c) => {
        if (c <= 1) {
          if (detailGraceTimer.current) { clearInterval(detailGraceTimer.current); detailGraceTimer.current = null; }
          setDetailPending(false);
          // 여기서 처음으로 실제 AI 요청 시작 (글로벌 태스크 → 이동해도 유지 + 완료 벨 알림)
          detailTask.start({
            issue_title: issueTitle,
            scenario_title: scenario.title,
            economic_analysis: scenario.economic_analysis,
            rising: scenario.rising_stocks ?? [],
            falling: scenario.falling_stocks ?? [],
          });
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  };

  // 5초 유예 중 취소 → 타이머만 정리, AI 호출 시작 안 함(토큰 미사용)
  const cancelDetailGrace = () => {
    if (detailGraceTimer.current) { clearInterval(detailGraceTimer.current); detailGraceTimer.current = null; }
    setDetailPending(false);
    setDetailCountdown(0);
  };

  const navigate = (ticker: string) => {
    if (isKrTicker(ticker)) {
      router.push(`/search?q=${ticker}&market=KR`);
    } else {
      router.push(`/search?q=${ticker}&market=US`);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* 기본 정보 */}
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", alignItems: "center" }}>
        <span style={{
          padding: "2px 10px", borderRadius: "10px", fontSize: "0.78rem", fontWeight: 700,
          background: scenario.market_direction === "강세" ? "rgba(255,60,60,0.15)" :
                      scenario.market_direction === "약세" ? "rgba(0,120,255,0.15)" : "rgba(255,180,50,0.15)",
          border: `1px solid ${scenario.market_direction === "강세" ? "var(--color-danger)" :
                               scenario.market_direction === "약세" ? "var(--color-primary)" : "var(--color-warning)"}`,
          color: scenario.market_direction === "강세" ? "var(--color-danger)" :
                 scenario.market_direction === "약세" ? "var(--color-primary)" : "var(--color-warning)",
        }}>
          {scenario.market_direction}
        </span>
        <span style={{ fontSize: "0.82rem", color: "var(--color-muted)" }}>확률: <strong style={{ color: "var(--color-text)" }}>{scenario.probability_pct}%</strong></span>
      </div>

      {/* 현실화 조건 */}
      {scenario.trigger && (
        <div style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--color-border)", borderRadius: "6px", padding: "10px 14px" }}>
          <div style={{ fontSize: "0.72rem", fontWeight: 800, color: "var(--color-muted)", marginBottom: "4px" }}>현실화 조건</div>
          <div style={{ fontSize: "0.85rem", color: "var(--color-text)", lineHeight: 1.5 }}>{scenario.trigger}</div>
        </div>
      )}

      {/* 경제 분석 */}
      {scenario.economic_analysis && (
        <div style={{ background: "rgba(0,0,0,0.2)", borderLeft: "3px solid var(--color-accent)", borderRadius: "0 6px 6px 0", padding: "10px 14px" }}>
          <div style={{ fontSize: "0.72rem", fontWeight: 800, color: "var(--color-muted)", marginBottom: "4px" }}>경제 분석</div>
          <div style={{ fontSize: "0.85rem", color: "var(--color-text)", lineHeight: 1.6 }}>{scenario.economic_analysis}</div>
        </div>
      )}

      {/* 전략 박스 */}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
        {scenario.short_strategy && <StrategyBox label="단타 전략" text={scenario.short_strategy} color="var(--color-warning)" />}
        {scenario.long_strategy  && <StrategyBox label="장타 전략" text={scenario.long_strategy}  color="var(--color-accent)" />}
      </div>

      {/* 상승 예상 종목 */}
      {(krRising.length > 0 || usRising.length > 0) && (
        <div>
          <SectionHeader title="🟢 상승 수혜주" count={(scenario.rising_stocks ?? []).length} />
          {krRising.length > 0 && (
            <div style={{ marginBottom: "8px" }}>
              <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", fontWeight: 700, marginBottom: "4px" }}>🇰🇷 국내</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                {krRising.map((s, i) => (
                  <StockRow key={i} stock={s} priceEntry={priceMap[s.ticker]} onClick={() => navigate(s.ticker)} />
                ))}
              </div>
            </div>
          )}
          {usRising.length > 0 && (
            <div>
              <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", fontWeight: 700, marginBottom: "4px" }}>🇺🇸 미국</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                {usRising.map((s, i) => (
                  <StockRow key={i} stock={s} priceEntry={priceMap[s.ticker]} onClick={() => navigate(s.ticker)} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 추가 관련주 (단타·중장기) — 강조 박스, 대장주(상승 수혜주) 바로 아래 배치 */}
      {themeStocks.length > 0 && (
        <div style={{
          background: "rgba(255,140,50,0.06)",
          border: "1px solid rgba(255,140,50,0.35)",
          borderRadius: "10px",
          padding: "12px 14px",
        }}>
          <SectionHeader title="🔥 추가 관련주 (단타 · 중장기)" count={themeStocks.length} />
          <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", marginBottom: "8px", lineHeight: 1.5 }}>
            대장주 외에 이 이슈로 수혜가 예상되는 종목 — <span style={{ color: "#ff8c32", fontWeight: 700 }}>⚡ 단타</span> 급등주와 <span style={{ color: "#5aa0ff", fontWeight: 700 }}>📆 중장기</span> 성장주를 함께 제시합니다.
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {themeStocks.map((s, i) => (
              <ThemeStockRow key={i} stock={s} priceEntry={priceMap[s.ticker]} onClick={() => navigate(s.ticker)} />
            ))}
          </div>
        </div>
      )}

      {/* 하락 예상 종목 */}
      {(krFalling.length > 0 || usFalling.length > 0) && (
        <div>
          <SectionHeader title="🔴 하락 위험주" count={(scenario.falling_stocks ?? []).length} />
          {krFalling.length > 0 && (
            <div style={{ marginBottom: "8px" }}>
              <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", fontWeight: 700, marginBottom: "4px" }}>🇰🇷 국내</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                {krFalling.map((s, i) => (
                  <StockRow key={i} stock={s} priceEntry={priceMap[s.ticker]} onClick={() => navigate(s.ticker)} />
                ))}
              </div>
            </div>
          )}
          {usFalling.length > 0 && (
            <div>
              <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", fontWeight: 700, marginBottom: "4px" }}>🇺🇸 미국</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                {usFalling.map((s, i) => (
                  <StockRow key={i} stock={s} priceEntry={priceMap[s.ticker]} onClick={() => navigate(s.ticker)} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 상세 분석 버튼 */}
      <div style={{ borderTop: "1px solid var(--color-border)", paddingTop: "1rem" }}>
        {detailStatus === "idle" && !detailPending && (
          <button
            className="stockcy-btn stockcy-btn-primary"
            style={{ width: "100%", padding: "10px", fontWeight: 700 }}
            onClick={startDetailWithGrace}
          >
            상세 분석보기 <span style={{ fontSize: "0.72rem", opacity: 0.85 }}>(AI 토큰 사용)</span>
          </button>
        )}
        {detailPending && (
          <div style={{ display: "flex", alignItems: "center", gap: "10px", justifyContent: "space-between", background: "rgba(251,191,36,0.1)", border: "1px solid rgba(251,191,36,0.4)", borderRadius: "8px", padding: "8px 12px" }}>
            <span style={{ fontSize: "0.82rem", color: "var(--color-text)" }}>
              ⏳ <b>{detailCountdown}초</b> 후 분석 시작 — 지금 취소하면 <b>토큰이 사용되지 않습니다</b>
            </span>
            <button
              className="stockcy-btn stockcy-btn-secondary"
              style={{ padding: "5px 12px", fontWeight: 700, flexShrink: 0, display: "flex", alignItems: "center", gap: "4px" }}
              onClick={cancelDetailGrace}
            >
              <X size={13} /> 취소
            </button>
          </div>
        )}
        {detailStatus === "running" && (
          <div style={{ display: "flex", alignItems: "center", gap: "8px", justifyContent: "center", color: "var(--color-muted)", fontSize: "0.85rem", padding: "10px" }}>
            <Loader2 className="animate-spin" size={18} /> {detailMsg || "상세 분석 중..."} <span style={{ fontSize: "0.72rem", opacity: 0.8 }}>(다른 화면으로 이동해도 계속 진행됩니다)</span>
          </div>
        )}
        {(detailStatus === "done" || detailStatus === "error") && (
          <div>
            <button
              className="stockcy-btn stockcy-btn-secondary"
              style={{ width: "100%", padding: "8px", fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}
              onClick={() => setShowDetail(v => !v)}
            >
              {showDetail ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {showDetail ? "상세 분석 접기" : "상세 분석 펼치기"}
            </button>
            {showDetail && (
              <div style={{ marginTop: "1rem", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "8px", padding: "1rem" }}>
                {detailStatus === "error"
                  ? <div style={{ color: "var(--color-danger)", fontSize: "0.85rem" }}>{detailMsg}</div>
                  : detailResult && <DetailPanel detail={detailResult} />
                }
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── 이슈 패널 ─────────────────────────────────────────────────────────────────
function IssuePanel({ issue }: { issue: Issue }) {
  const [scenarioIdx, setScenarioIdx] = useState(0);
  const scenarios = issue.scenarios ?? [];
  const activeScenario = scenarios[scenarioIdx];

  const urgencyColor = (u?: string) => {
    if (u === "긴급") return "var(--color-danger)";
    if (u === "보통") return "var(--color-warning)";
    return "var(--color-muted)";
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* 이슈 헤더 */}
      <div>
        <div style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap", marginBottom: "6px" }}>
          {issue.urgency && (
            <span style={{
              padding: "1px 8px", borderRadius: "10px", fontSize: "0.72rem", fontWeight: 800,
              background: `${urgencyColor(issue.urgency)}22`,
              border: `1px solid ${urgencyColor(issue.urgency)}`,
              color: urgencyColor(issue.urgency),
            }}>
              {issue.urgency}
            </span>
          )}
          {issue.category && (
            <span style={{
              padding: "1px 8px", borderRadius: "10px", fontSize: "0.72rem", fontWeight: 700,
              background: "rgba(255,255,255,0.06)",
              border: "1px solid var(--color-border)",
              color: "var(--color-muted)",
            }}>
              {issue.category}
            </span>
          )}
        </div>
        <h2 style={{ fontSize: "1.1rem", fontWeight: 800, margin: "0 0 8px 0", color: "var(--color-text)" }}>
          {issue.title}
        </h2>
        {issue.summary && (
          <div style={{ background: "rgba(255,60,60,0.08)", borderLeft: "3px solid var(--color-danger)", padding: "10px 14px", borderRadius: "0 6px 6px 0", fontSize: "0.9rem", color: "var(--color-text)", lineHeight: 1.6 }}>
            {issue.summary}
          </div>
        )}
      </div>

      {/* 시나리오 탭 */}
      {scenarios.length > 0 && (
        <div>
          <div style={{ display: "flex", gap: "6px", marginBottom: "1rem" }}>
            {scenarios.map((sc, idx) => (
              <button
                key={idx}
                onClick={() => setScenarioIdx(idx)}
                style={{
                  padding: "6px 14px", fontWeight: 700, fontSize: "0.85rem", borderRadius: "6px",
                  border: "1px solid",
                  borderColor: scenarioIdx === idx ? "var(--color-accent)" : "var(--color-border)",
                  background: scenarioIdx === idx ? "rgba(255,255,255,0.08)" : "transparent",
                  color: scenarioIdx === idx ? "var(--color-text)" : "var(--color-muted)",
                  cursor: "pointer",
                  transition: "0.15s",
                }}
              >
                시나리오 {sc.label}: {sc.title} ({sc.probability_pct}%)
              </button>
            ))}
          </div>
          {activeScenario && <ScenarioContent scenario={activeScenario} issueTitle={issue.title} />}
        </div>
      )}
    </div>
  );
}

// ── 에이전트 오늘의 이슈 패널 ─────────────────────────────────────────────────
function AgentDailyIssuesPanel() {
  const [refreshing, setRefreshing] = useState(false);
  const { data, mutate } = useSWR(
    "/backend/api/ai/agent-daily-issues?days=2",
    (url: string) => fetch(url).then(r => r.json()),
    { refreshInterval: 300000 }
  );
  const issues = data?.issues ?? [];

  const refresh = async () => {
    setRefreshing(true);
    try {
      const token = getToken();
      await fetch("/backend/api/ai/agent-daily-issues/refresh", {
        method: "POST",
        headers: {
          "ngrok-skip-browser-warning": "69420",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      await mutate();
    } catch {}
    setRefreshing(false);
  };

  const sentColor = (s: string) => {
    if ((s ?? "").includes("긍정")) return "#34d399";
    if ((s ?? "").includes("부정")) return "#f87171";
    return "#fbbf24";
  };

  return (
    <div className="stockcy-card" style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ fontSize: "0.82rem", fontWeight: 800, color: "#a5b4fc" }}>🤖 에이전트 오늘의 이슈</div>
        <button
          onClick={refresh}
          disabled={refreshing}
          style={{ fontSize: "0.68rem", padding: "3px 8px", background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.35)", color: "#a5b4fc", borderRadius: "4px", fontWeight: 700, cursor: refreshing ? "wait" : "pointer" }}
        >
          {refreshing ? "분석 중..." : "갱신"}
        </button>
      </div>
      <div style={{ fontSize: "0.66rem", color: "var(--color-muted)" }}>
        에이전트가 매일 아침 자동 분석하는 이슈입니다. 이 종목 판단의 근거로도 쓰입니다.
      </div>
      {issues.length === 0 ? (
        <div style={{ fontSize: "0.7rem", color: "var(--color-muted)", padding: "0.4rem 0" }}>
          아직 분석된 이슈가 없습니다. "갱신"을 누르거나 평일 아침 자동 분석을 기다리세요.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "5px", maxHeight: "320px", overflowY: "auto" }}>
          {issues.map((iss: any, i: number) => (
            <div key={i} style={{ background: "rgba(255,255,255,0.02)", borderLeft: `3px solid ${sentColor(iss.sentiment)}`, borderRadius: "4px", padding: "6px 8px" }}>
              <div style={{ fontSize: "0.74rem", fontWeight: 700, color: "var(--color-text)" }}>{iss.title}</div>
              <div style={{ display: "flex", gap: "6px", marginTop: "2px", flexWrap: "wrap" }}>
                {iss.theme && <span style={{ fontSize: "0.62rem", padding: "1px 5px", borderRadius: "3px", background: "rgba(99,102,241,0.12)", color: "#a5b4fc" }}>{iss.theme}</span>}
                {iss.sentiment && <span style={{ fontSize: "0.62rem", color: sentColor(iss.sentiment) }}>{iss.sentiment}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── AI 기능별 실적 통합 비교 ──────────────────────────────────────────────────
function AiPerformanceCompare() {
  const [feats, setFeats] = useState<any[] | null>(null);
  const [bestKey, setBestKey] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/backend/api/ai/performance-summary");
        if (!res.ok) return;
        const txt = await res.text();
        try {
          const j = JSON.parse(txt);
          setFeats(j.features ?? []);
          setBestKey(j.best_key ?? null);
        } catch { /* 비-JSON 무시 */ }
      } catch { /* 네트워크 오류 무시 */ }
    })();
  }, []);

  if (!feats) return null;
  const hasData = feats.some((f: any) => f.n > 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px", paddingBottom: "8px", borderBottom: "1px solid rgba(255,255,255,0.08)", marginBottom: "2px" }}>
      <div style={{ fontSize: "0.72rem", fontWeight: 800, color: "var(--color-text)" }}>🏆 AI 기능별 실적 비교</div>
      <div style={{ display: "flex", gap: "6px" }}>
        {feats.map((f: any) => {
          const isBest = f.key === bestKey && f.n > 0;
          const rc = f.avg_return > 0 ? "#34d399" : f.avg_return < 0 ? "#f87171" : "var(--color-muted)";
          return (
            <div key={f.key} style={{
              flex: 1,
              background: isBest ? "rgba(52,211,153,0.12)" : "rgba(255,255,255,0.03)",
              border: `1px solid ${isBest ? "#34d399" : "rgba(255,255,255,0.1)"}`,
              borderRadius: "6px", padding: "6px 7px",
            }}>
              <div style={{ fontSize: "0.66rem", fontWeight: 800, color: "var(--color-text)", display: "flex", alignItems: "center", gap: "3px" }}>
                {isBest && <span>👑</span>}{f.label}
              </div>
              {f.n > 0 ? (
                <>
                  <div style={{ fontSize: "0.78rem", fontWeight: 800, color: rc }}>승률 {f.win_rate}%</div>
                  <div style={{ fontSize: "0.6rem", color: "var(--color-muted)" }}>
                    평균 <span style={{ color: rc }}>{f.avg_return >= 0 ? "+" : ""}{f.avg_return}%</span> · {f.n}건
                  </div>
                  <div style={{ fontSize: "0.56rem", color: "var(--color-muted)" }}>{f.metric}</div>
                </>
              ) : (
                <div style={{ fontSize: "0.6rem", color: "var(--color-muted)", paddingTop: "4px" }}>데이터 누적 중</div>
              )}
            </div>
          );
        })}
      </div>
      {!hasData && (
        <div style={{ fontSize: "0.58rem", color: "var(--color-muted)" }}>
          ※ 각 기능의 사후 성과가 쌓이면(시나리오 d7·스크리너 d3·에이전트 매도확정) 자동 표시됩니다.
        </div>
      )}
    </div>
  );
}

// ── 시나리오 적중률 패널 ──────────────────────────────────────────────────────
export function ScenarioTrackingPanel() {
  const [running, setRunning] = useState(false);
  const [data, setData] = useState<any>(null);
  const [msg, setMsg] = useState("");

  // 추적 중인 종목 목록 (펼쳐보기) — 무거우니 펼칠 때 최초 1회만 로드
  const [list, setList] = useState<any[]>([]);
  const [listOpen, setListOpen] = useState(false);
  const [listLoaded, setListLoaded] = useState(false);
  const [listLoading, setListLoading] = useState(false);

  const loadList = async () => {
    setListLoading(true);
    try {
      const res = await fetch("/backend/api/ai/scenario-tracking/list");
      if (res.ok) {
        const txt = await res.text();
        try { setList(JSON.parse(txt)); setListLoaded(true); } catch { /* 비-JSON 무시 */ }
      }
    } catch { /* 네트워크 오류 무시 */ }
    finally { setListLoading(false); }
  };

  const toggleList = () => {
    const next = !listOpen;
    setListOpen(next);
    if (next && !listLoaded) loadList();
  };

  // 통계만 빠르게 조회 (가격 재추적 없음). 비-JSON 응답에도 안전.
  const loadStats = async () => {
    try {
      const res = await fetch("/backend/api/ai/scenario-tracking/stats");
      if (!res.ok) return;
      const txt = await res.text();
      try { setData(JSON.parse(txt)); } catch { /* 비-JSON 무시 */ }
    } catch { /* 네트워크 오류 무시 */ }
  };

  const runTracking = async () => {
    setRunning(true);
    setMsg("가격 추적 중... (수십 초 걸릴 수 있어요)");
    try {
      const res = await fetch("/backend/api/ai/scenario-tracking/run", { method: "POST" });
      const txt = await res.text();
      let json: any = null;
      try { json = JSON.parse(txt); } catch { /* 비-JSON */ }
      if (res.ok && json) {
        setData(json);
        setMsg(`✅ 신규 ${json.updated_now ?? 0}건 추적 완료`);
      } else {
        // 추적이 길어 프록시 연결이 끊겨도 서버에서는 계속 진행됨 → 잠시 후 통계만 갱신
        setMsg("⏳ 추적이 길어 백그라운드에서 계속됩니다. 잠시 후 통계를 갱신합니다...");
        setTimeout(loadStats, 5000);
      }
    } catch {
      setMsg("⏳ 추적이 길어 백그라운드에서 계속됩니다. 잠시 후 통계를 갱신합니다...");
      setTimeout(loadStats, 5000);
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => { loadStats(); }, []);

  const byScenario = data?.by_scenario ?? [];
  const byHorizon = data?.by_horizon ?? [];
  const winners = data?.top_winners ?? [];
  const losers = data?.top_losers ?? [];

  // 추적 목록: 등장 날짜별로 묶고(최신 날짜 먼저), 그룹 안에서는 현재 수익률 높은 순
  const groupedByDate = useMemo(() => {
    const map = new Map<string, any[]>();
    for (const s of list) {
      const d = String(s.captured_at ?? "").slice(0, 10) || "날짜 미상";
      if (!map.has(d)) map.set(d, []);
      map.get(d)!.push(s);
    }
    return [...map.keys()].sort((a, b) => b.localeCompare(a)).map((d) => ({
      date: d,
      items: map.get(d)!.sort((a: any, b: any) => {
        const ar = a.current_return, br = b.current_return;
        if (ar == null && br == null) return 0;
        if (ar == null) return 1;
        if (br == null) return -1;
        return br - ar;
      }),
    }));
  }, [list]);

  return (
    <div className="stockcy-card" style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ fontSize: "0.82rem", fontWeight: 800, color: "var(--color-muted)" }}>📊 시나리오 적중률</div>
        <button
          onClick={runTracking}
          disabled={running}
          style={{ fontSize: "0.68rem", padding: "3px 8px", background: "rgba(168,85,247,0.15)", border: "1px solid rgba(168,85,247,0.35)", color: "#c084fc", borderRadius: "4px", fontWeight: 700, cursor: running ? "wait" : "pointer" }}
        >
          {running ? "..." : "추적 실행"}
        </button>
      </div>

      <AiPerformanceCompare />

      {msg && <div style={{ fontSize: "0.68rem", color: "var(--color-muted)" }}>{msg}</div>}

      <div style={{ fontSize: "0.6rem", color: "var(--color-muted)", lineHeight: 1.4 }}>
        ※ 적중 = 방향성 기준 (수혜·테마주는 상승 시, 하락 위험주는 하락 시 적중)
      </div>

      {byHorizon.length > 0 && (
        <div style={{ display: "flex", gap: "6px" }}>
          {byHorizon.map((h: any) => {
            const isLong = h.horizon === "중장기";
            return (
              <div key={h.horizon} style={{
                flex: 1,
                background: isLong ? "rgba(80,160,255,0.1)" : "rgba(255,140,50,0.1)",
                border: `1px solid ${isLong ? "#5aa0ff" : "#ff8c32"}`,
                borderRadius: "6px", padding: "6px 8px",
              }}>
                <div style={{ fontSize: "0.66rem", fontWeight: 800, color: isLong ? "#5aa0ff" : "#ff8c32" }}>
                  {isLong ? "📆 중장기" : "⚡ 단타"} ({h.count})
                </div>
                <div style={{ fontSize: "0.62rem", color: "var(--color-muted)" }}>
                  {isLong ? "7일 승률" : "3일 승률"} {isLong ? h.win_rate_d7 : h.win_rate_d3}%
                </div>
              </div>
            );
          })}
        </div>
      )}

      {byScenario.length === 0 ? (
        <div style={{ fontSize: "0.7rem", color: "var(--color-muted)", padding: "0.4rem 0" }}>
          시나리오 검색 후 1일 이상 경과한 종목부터 통계 표시.
        </div>
      ) : (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {byScenario.slice(0, 5).map((s: any) => {
              const c = s.avg_d3_return > 0 ? "#34d399" : s.avg_d3_return < 0 ? "#f87171" : "var(--color-muted)";
              return (
                <div key={s.keyword} style={{ background: "rgba(255,255,255,0.02)", padding: "4px 6px", borderRadius: "4px", fontSize: "0.7rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ color: "var(--color-text)", fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "65%" }}>{s.keyword}</span>
                    <span style={{ color: c, fontWeight: 700 }}>{s.avg_d3_return >= 0 ? "+" : ""}{s.avg_d3_return}%</span>
                  </div>
                  <div style={{ fontSize: "0.62rem", color: "var(--color-muted)" }}>{s.count}종목 · 3일 승률 {s.win_rate_d3}%</div>
                </div>
              );
            })}
          </div>

          {winners.length > 0 && (
            <div>
              <div style={{ fontSize: "0.65rem", color: "var(--color-muted)", marginBottom: "3px", fontWeight: 700 }}>🏆 7일 최고 수익</div>
              {winners.slice(0, 3).map((w: any, i: number) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.65rem", padding: "1px 4px" }}>
                  <span style={{ color: "var(--color-text)", fontWeight: 600 }}>{w.name}</span>
                  <span style={{ color: "#34d399", fontWeight: 700 }}>+{w.d7_return}%</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* 추적 중인 종목 — 별도 모달 창으로 보기 */}
      <div style={{ borderTop: "1px solid var(--color-border)", paddingTop: "6px", marginTop: "2px" }}>
        <button
          onClick={toggleList}
          className="stockcy-btn stockcy-btn-secondary"
          style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: "6px", fontSize: "0.72rem", fontWeight: 700, padding: "6px 0" }}
        >
          🔎 추적 중인 종목{listLoaded ? ` ${list.length}건` : ""} 전체보기 ↗
        </button>
      </div>

      {/* 추적 종목 모달 (화면 위 별도 창) */}
      {listOpen && (
        <div
          onClick={() => setListOpen(false)}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center", padding: "20px" }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{ background: "var(--color-surface)", borderRadius: "12px", width: "92%", maxWidth: "920px", maxHeight: "88vh", display: "flex", flexDirection: "column", border: "1px solid var(--color-border)", boxShadow: "0 10px 40px rgba(0,0,0,0.5)" }}
          >
            {/* 헤더 */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "16px 20px", borderBottom: "1px solid var(--color-border)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <h2 style={{ fontSize: "1.05rem", fontWeight: 800, margin: 0 }}>🔎 추적 중인 시나리오 종목</h2>
                {listLoaded && <span style={{ fontSize: "0.8rem", color: "var(--color-muted)" }}>{list.length}건</span>}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "4px 10px", fontSize: "0.72rem" }} onClick={loadList} disabled={listLoading}>새로고침</button>
                <button className="stockcy-btn" style={{ padding: "4px 10px" }} onClick={() => setListOpen(false)}>✕</button>
              </div>
            </div>

            <div style={{ padding: "10px 20px 4px", fontSize: "0.7rem", color: "var(--color-muted)", lineHeight: 1.6 }}>
              📅 <b>등장 날짜별</b>로 묶임(최신순). 왼쪽 배지 = 시나리오가 맞았는지: <span style={{ color: "#34d399" }}>✅적중</span>(예상대로 움직임) · <span style={{ color: "#f87171" }}>❌빗나감</span>(반대로 움직임) · <span style={{ color: "#fbbf24" }}>⏳진행중</span>(보합) · <span style={{ color: "#fbbf24" }}>추적중</span>(등장가/가격 집계 전)<br/>
              · <b>📈상승기대</b>(수혜)는 오르면 적중, <b>📉하락기대</b>(피해)는 내리면 적중 · 오른쪽 숫자 = <b>등장가 대비 현재 수익률</b> · <b>7일확정</b>=등장 후 7거래일 성과
            </div>

            {/* 본문 (날짜 그룹별, 스크롤) */}
            <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "8px 20px 20px", display: "flex", flexDirection: "column", gap: "12px" }}>
              {listLoading ? (
                <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-muted)" }}>불러오는 중...</div>
              ) : list.length === 0 ? (
                <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-muted)" }}>추적 중인 종목이 없습니다.</div>
              ) : (
                groupedByDate.map((group) => (
                  <div key={group.date} style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <div style={{ position: "sticky", top: 0, background: "var(--color-card)", zIndex: 1, fontSize: "0.78rem", fontWeight: 800, color: "var(--color-text)", padding: "4px 2px", borderBottom: "1px solid var(--color-border)" }}>
                      📅 {group.date} <span style={{ fontSize: "0.7rem", fontWeight: 600, color: "var(--color-muted)" }}>· {group.items.length}종목</span>
                    </div>
                    {group.items.map((s: any, i: number) => {
                      const isUs = /[A-Za-z]/.test(String(s.ticker));
                      const cr = s.current_return;
                      const crColor = cr == null ? "var(--color-muted)" : cr >= 0 ? "#34d399" : "#f87171";
                      const sceneText = String(s.scenario_title || s.scenario_keyword || "").trim();
                      // 적중 판정: 수혜/테마=상승 기대, 피해=하락 기대. 결과는 현재수익률(없으면 7일).
                      const outcome = cr != null ? cr : (s.d7_return ?? null);
                      const expectUp = s.role !== "피해";
                      let vt: { t: string; c: string; bg: string };
                      if (outcome == null) vt = { t: "추적중", c: "#fbbf24", bg: "rgba(251,191,36,0.12)" };
                      else {
                        const hit  = expectUp ? outcome > 1 : outcome < -1;
                        const miss = expectUp ? outcome < -1 : outcome > 1;
                        vt = hit  ? { t: "✅ 적중",   c: "#34d399", bg: "rgba(52,211,153,0.15)" }
                           : miss ? { t: "❌ 빗나감", c: "#f87171", bg: "rgba(248,113,113,0.15)" }
                           :        { t: "⏳ 진행중", c: "#fbbf24", bg: "rgba(251,191,36,0.12)" };
                      }
                      const roleLabel = s.role === "피해" ? "📉 하락기대" : s.role === "수혜" ? "📈 상승기대" : s.role === "테마" ? "테마" : s.role;
                      return (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: "12px", background: "rgba(255,255,255,0.03)", border: "1px solid var(--color-border)", borderLeft: `4px solid ${vt.c}`, borderRadius: "8px", padding: "10px 14px" }}>
                          {/* 적중 상태 배지 */}
                          <div style={{ flexShrink: 0, minWidth: "70px", textAlign: "center", background: vt.bg, border: `1px solid ${vt.c}55`, borderRadius: "8px", padding: "6px 4px" }}>
                            <div style={{ fontSize: "0.78rem", fontWeight: 800, color: vt.c, whiteSpace: "nowrap" }}>{vt.t}</div>
                          </div>
                          {/* 종목 정보 */}
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap", marginBottom: "2px" }}>
                              <span style={{ fontWeight: 800, color: "var(--color-text)", fontSize: "0.95rem" }}>{s.name}</span>
                              <span style={{ color: "var(--color-muted)", fontSize: "0.74rem" }}>{s.ticker}</span>
                              {isUs && <span style={{ fontSize: "0.62rem", padding: "1px 5px", borderRadius: "3px", background: "rgba(50,200,100,0.15)", color: "#34d399", border: "1px solid rgba(50,200,100,0.3)" }}>US</span>}
                              {s.role && <span style={{ fontSize: "0.62rem", padding: "1px 5px", borderRadius: "3px", color: expectUp ? "#34d399" : "#f87171", border: `1px solid ${(expectUp ? "#34d399" : "#f87171")}55` }}>{roleLabel}</span>}
                              {s.horizon && <span style={{ fontSize: "0.62rem", padding: "1px 5px", borderRadius: "3px", color: "var(--color-muted)", border: "1px solid var(--color-border)" }}>{s.horizon}</span>}
                            </div>
                            {sceneText && (
                              <div title={sceneText} style={{ fontSize: "0.74rem", color: "var(--color-subtle)", display: "-webkit-box", WebkitBoxOrient: "vertical", WebkitLineClamp: 1, overflow: "hidden", wordBreak: "keep-all", lineHeight: 1.3 }}>
                                🧩 {sceneText}
                              </div>
                            )}
                            <div style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>
                              {s.captured_price
                                ? <>등장가 {isUs ? "$" : "₩"}{Number(s.captured_price).toLocaleString()}{s.current_price != null && <> → 현재 {isUs ? "$" : "₩"}{Number(s.current_price).toLocaleString()}</>}</>
                                : <span style={{ color: "#fbbf24" }}>등장가 집계 대기 (다음 새벽 확정)</span>}
                            </div>
                          </div>
                          {/* 등장 후 수익률 (대표 숫자) + 7일 확정 */}
                          <div style={{ textAlign: "right", flexShrink: 0, minWidth: "84px" }}>
                            <div style={{ color: crColor, fontWeight: 900, fontSize: "1.15rem", whiteSpace: "nowrap" }}>
                              {cr != null ? `${cr >= 0 ? "+" : ""}${cr}%` : "—"}
                            </div>
                            <div style={{ fontSize: "0.6rem", color: "var(--color-muted)" }}>등장 후</div>
                            {s.d7_return != null && (
                              <div style={{ fontSize: "0.64rem", color: "var(--color-subtle)", marginTop: "1px" }}>7일확정 {s.d7_return >= 0 ? "+" : ""}{s.d7_return}%</div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ── 지역 분류 헬퍼 ────────────────────────────────────────────────────────────
type RegionFilter = "전체" | "글로벌" | "국내" | "이머징마켓" | "커스텀" | "에이전트";

function classifyIssueRegion(issue: Issue): "글로벌" | "국내" | "이머징마켓" | "mixed" {
  const cat = (issue.category ?? "").toLowerCase();
  if (cat.includes("암호화폐") || cat.includes("지정학") || cat.includes("이머징")) return "이머징마켓";
  let krCount = 0, usCount = 0;
  for (const sc of issue.scenarios ?? []) {
    for (const s of [...(sc.rising_stocks ?? []), ...(sc.falling_stocks ?? [])]) {
      if (isKrTicker(s.ticker)) krCount++; else usCount++;
    }
  }
  if (usCount > krCount) return "글로벌";
  if (krCount > usCount) return "국내";
  return "mixed";
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
const SC_DATA_KEY = "stockcy_scenarios_data";
const SC_TS_KEY   = "stockcy_scenarios_ts";

// ── 시장 해설 카드 (왜 지금 장이 이렇게 움직이나) ───────────────────────────────
function MarketCommentaryCard() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [data, setData] = useState<any>(null);
  const [status, setStatus] = useState<"loading" | "done" | "error">("loading");
  const [open, setOpen] = useState(false);   // 기본 접힘 — 클릭해야 펼쳐짐
  const [seen, setSeen] = useState(false);    // 펼쳐서 읽으면 true (초록불 끔)

  const load = useCallback(async (refresh = false) => {
    if (refresh) setSeen(false);   // 새로 생성하면 다시 '업데이트 있음'
    setStatus("loading");
    try {
      const token = getToken();
      const res = await fetch(`/backend/api/ai/market-commentary${refresh ? "?refresh=true" : ""}`, {
        headers: {
          "ngrok-skip-browser-warning": "69420",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!res.ok || !res.body) { setStatus("error"); return; }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";
        for (const part of parts) {
          const t = part.trim();
          if (!t.startsWith("data:")) continue;
          try {
            const d = JSON.parse(t.slice(5).trim());
            if (d.status === "done" && d.result) { setData(d.result); setStatus("done"); }
            else if (d.status === "error") setStatus("error");
          } catch { /* 비-JSON 무시 */ }
        }
      }
    } catch { setStatus("error"); }
  }, []);

  useEffect(() => { load(false); }, [load]);

  return (
    <div style={{ border: "1px solid rgba(96,165,250,0.35)", background: "rgba(96,165,250,0.06)", borderRadius: "12px", padding: "1rem 1.25rem", marginBottom: "1.25rem" }}>
      <style>{`@keyframes mcBlink{0%,100%{opacity:1}50%{opacity:0.25}}`}</style>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontWeight: 800, fontSize: "0.98rem", color: "var(--color-text)" }}>
          📰 시장 해설 <span style={{ fontSize: "0.76rem", color: "var(--color-muted)", fontWeight: 600 }}>왜 지금 장이 이렇게 움직이나</span>
          <AiCostBadge small />
          {status === "done" && data && !data.error && !seen && (
            <span title="새 시장 해설 업데이트 — 펴기" style={{ width: 9, height: 9, borderRadius: "50%", background: "#34d399", boxShadow: "0 0 6px 1px rgba(52,211,153,0.7)", display: "inline-block", animation: "mcBlink 1.1s infinite" }} />
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          {isAdmin ? (
            <button onClick={() => load(true)} disabled={status === "loading"} className="stockcy-btn stockcy-btn-secondary" style={{ padding: "3px 9px", fontSize: "0.72rem" }} title="새로 생성">
              <RefreshCw size={12} />
            </button>
          ) : (
            <span style={{ fontSize: "0.68rem", color: "var(--color-muted)" }} title="시장 해설은 관리자가 생성한 내용을 읽기 전용으로 제공합니다.">읽기 전용</span>
          )}
          <button onClick={() => { setOpen(o => !o); setSeen(true); }} className="stockcy-btn stockcy-btn-secondary" style={{ padding: "3px 9px", fontSize: "0.72rem" }}>
            {open ? "접기" : "펴기"}
          </button>
        </div>
      </div>

      {open && (
        <div style={{ marginTop: "0.75rem" }}>
          {status === "loading" ? (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--color-muted)", fontSize: "0.85rem" }}>
              <Loader2 className="animate-spin" size={16} /> 시장 구조·수급·심리 분석 중... (수십 초)
            </div>
          ) : status === "error" || !data || data.error ? (
            <div style={{ color: "var(--color-muted)", fontSize: "0.85rem" }}>
              {isAdmin ? "해설을 불러오지 못했습니다." : "아직 생성된 시장 해설이 없습니다. 관리자가 생성하면 표시됩니다."} <button onClick={() => load(isAdmin)} style={{ color: "var(--color-accent)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>다시 시도</button>
            </div>
          ) : (
            <>
              <div style={{ fontWeight: 800, fontSize: "1.05rem", color: "var(--color-text)", marginBottom: "0.5rem" }}>{data.title}</div>
              <MarkdownLite text={data.commentary} style={{ lineHeight: 1.75, fontSize: "0.88rem", color: "var(--color-subtle)" }} />
              {data.generated_at && (
                <div style={{ marginTop: "0.6rem", fontSize: "0.7rem", color: "var(--color-muted)" }}>🕒 {data.generated_at} 기준 · AI 검색 분석 (참고용, 투자 판단은 본인 책임)</div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ScenariosPageInner() {
  const { setReady } = useAnalysisReady();
  const { notifyDone } = useAiTask();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";   // 시나리오 생성은 관리자만, 일반 유저는 읽기 전용

  const isMobile = useIsMobile();
  const [sidebarOpen, setSidebarOpen] = useState(false);  // 모바일에서 부가 정보(좌측) 접기/펼치기
  const [mounted, setMounted] = useState(false);
  const [loading, setLoading]     = useState(false);
  const [statusMsg, setStatusMsg] = useState("AI 모델에 연결 중...");
  const [issues, setIssues]       = useState<Issue[]>([]);
  const [lastUpdated, setLastUpdated] = useState<string>("");
  const [issueIdx, setIssueIdx]   = useState(0);
  const [loadError, setLoadError] = useState("");
  const [regionFilter, setRegionFilter] = useState<RegionFilter>("전체");
  const [fetchTrigger, setFetchTrigger] = useState<number | null>(null);

  // 커스텀 이슈 · 최근 검색어 — 서버(계정별)에 영속. (CUSTOM_KEY/RECENT_KEY는 레거시 localStorage 1회 이관용)
  const CUSTOM_KEY   = "stockcy_custom_issues";
  const RECENT_KEY   = "stockcy_recent_searches";
  const [customKeyword, setCustomKeyword] = useState("");
  const [customLoading, setCustomLoading] = useState(false);
  const [customError, setCustomError]     = useState("");
  const [insightTab, setInsightTab]       = useState<"scenario" | "insight">("scenario");
  const [showRecent, setShowRecent]       = useState(false);

  const [customIssues, setCustomIssues] = useState<Array<Issue & { isCustom: true; keyword: string; id?: number }>>([]);
  const [recentSearches, setRecentSearches] = useState<string[]>([]);

  // 에이전트가 자동 생성한 오늘의 시나리오 (네가 AI업데이트 안 눌러도 자동 표시)
  const { data: agentScenarioData } = useSWR(
    "/backend/api/ai/agent-scenarios?days=1",
    (url: string) => fetch(url).then(r => r.json()),
    { refreshInterval: 300000 }
  );
  const agentScenarios: any[] = (agentScenarioData?.scenarios ?? []).map((s: any) => ({
    ...s,
    isAgent: true,
    keyword: s._keyword,
  }));

  // 마운트 직후 localStorage 안전 조회 (Hydration Mismatch 방지)
  useEffect(() => {
    setMounted(true);
    try {
      const savedIssues = localStorage.getItem(SC_DATA_KEY);
      if (savedIssues) {
        const parsed = JSON.parse(savedIssues);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setIssues(parsed);
        } else {
          // 빈 배열 등 비정상 캐시 제거 (구버전 코드가 저장한 경우)
          localStorage.removeItem(SC_DATA_KEY);
          localStorage.removeItem(SC_TS_KEY);
        }
      }

      const savedTs = localStorage.getItem(SC_TS_KEY);
      if (savedTs) setLastUpdated(savedTs);
    } catch (e) {
      console.error("[Scenarios] LocalStorage load failed:", e);
    }
  }, []);

  // 커스텀 시나리오 · 최근 검색어 — 서버(계정별)에서 로드.
  // 과거 브라우저 localStorage에 남아있던 데이터는 1회 서버로 이관 후 제거한다.
  useEffect(() => {
    if (!mounted) return;
    let cancelled = false;
    (async () => {
      try {
        // (1) 레거시 localStorage → 서버 1회 이관
        try {
          const legacyCustom = localStorage.getItem(CUSTOM_KEY);
          if (legacyCustom) {
            const arr = JSON.parse(legacyCustom);
            if (Array.isArray(arr)) {
              for (const it of arr) {  // 오래된→최신 순 그대로
                if (it && Array.isArray(it.scenarios) && it.scenarios.length > 0) {
                  await api.scenarios.saveCustom(it.keyword || it.title || "커스텀 이슈", it.title || it.keyword || "", it, it.searchedAt || "");
                }
              }
            }
            localStorage.removeItem(CUSTOM_KEY);
          }
          const legacyRecent = localStorage.getItem(RECENT_KEY);
          if (legacyRecent) {
            const arr = JSON.parse(legacyRecent);
            if (Array.isArray(arr)) {
              for (const kw of [...arr].reverse()) {  // 최신이 마지막에 저장되도록 역순
                if (kw) await api.scenarios.saveRecent(String(kw));
              }
            }
            localStorage.removeItem(RECENT_KEY);
          }
        } catch { /* 이관 실패는 무시 */ }

        // (2) 서버에서 로드 — 부분 실패 허용(한쪽 타임아웃/524여도 다른쪽은 반영). 비치명적이라 조용히 경고만.
        const [custom, recent] = await Promise.allSettled([
          api.scenarios.loadCustom(),
          api.scenarios.loadRecent(),
        ]);
        if (!cancelled) {
          if (custom.status === "fulfilled") setCustomIssues(custom.value as any);
          else console.warn("[Scenarios] 커스텀 시나리오 로드 건너뜀:", custom.reason?.message ?? custom.reason);
          if (recent.status === "fulfilled") setRecentSearches(recent.value);
        }
      } catch (e) {
        console.warn("[Scenarios] 서버 유저데이터 로드 실패(무시):", e);
      }
    })();
    return () => { cancelled = true; };
  }, [mounted]);

  // 마운트 시: 서버 캐시(오늘 자동 생성된 최신 시나리오)를 가볍게 동기화 — 비용 0 (캐시 사용)
  // localStorage에 옛 데이터가 있어도 서버에 더 최신 캐시가 있으면 화면을 갱신한다.
  useEffect(() => {
    if (!mounted) return;
    let cancelled = false;
    (async () => {
      try {
        const result = await readSSE(`/api/ai/scenarios?use_cache=true`, "GET");
        if (cancelled) return;
        const serverIssues = result?.issues ?? [];
        if (serverIssues.length > 0) {
          setIssues(serverIssues);
          const now = new Date().toLocaleString("ko-KR");
          setLastUpdated(now);
          try {
            localStorage.setItem(SC_DATA_KEY, JSON.stringify(serverIssues));
            localStorage.setItem(SC_TS_KEY, now);
          } catch {}
          setReady("scenarios", true);
        } else {
          // 서버에도 캐시가 없으면 → localStorage도 비었을 때만 신규 분석
          const stored = localStorage.getItem(SC_DATA_KEY);
          const parsed = stored ? JSON.parse(stored) : null;
          if (!parsed || !Array.isArray(parsed) || parsed.length === 0) {
            setFetchTrigger(0);
          }
        }
      } catch {
        // 서버 동기화 실패 시 기존 동작 유지
        try {
          const stored = localStorage.getItem(SC_DATA_KEY);
          const parsed = stored ? JSON.parse(stored) : null;
          if (!parsed || !Array.isArray(parsed) || parsed.length === 0) {
            setFetchTrigger(0);
          }
        } catch { setFetchTrigger(0); }
      }
    })();
    return () => { cancelled = true; };
  }, [mounted]);

  const { data: us } = useSWR("us-indices", () => api.us.indices() as Promise<any>, { refreshInterval: 60000 });
  const { data: fxRate } = useSWR("sc-usd-krw", () => api.us.exchangeRate(), { refreshInterval: 300000, revalidateOnFocus: false });
  const { data: tnx } = useSWR("sc-treasury-10y", () => api.us.treasury10y(), { refreshInterval: 300000, revalidateOnFocus: false });

  // fetchTrigger가 null이 아닐 때만 실행
  useEffect(() => {
    if (fetchTrigger === null) return;
    let cancelled = false;
    setLoading(true);
    setLoadError("");
    setStatusMsg("AI 시나리오 분석 중...");
    setIssueIdx(0);
    setReady("scenarios", false);

    // 최대 3분 후 자동 타임아웃 (서버 무응답 시 로딩 영구 대기 방지)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => { if (!cancelled) controller.abort(); }, 180_000);

    (async () => {
      try {
        const result = await readSSE(
          `/api/ai/scenarios?use_cache=false`,
          "GET",
          undefined,
          (msg) => { if (!cancelled) setStatusMsg(msg); },
          controller.signal
        );
        if (!cancelled) {
          if (result?.error) {
            setLoadError(`AI 분석 오류: ${result.error}`);
            setLoading(false);
            return;
          }
          const newIssues = result?.issues ?? [];
          if (newIssues.length === 0) {
            setLoadError("AI 분석 결과를 받지 못했습니다. 잠시 후 다시 시도해주세요.");
            setLoading(false);
            return;
          }
          setIssues(newIssues);
          const ts = new Date().toLocaleString("ko-KR");
          setLastUpdated(ts);
          try {
            localStorage.setItem(SC_DATA_KEY, JSON.stringify(newIssues));
            localStorage.setItem(SC_TS_KEY, ts);
          } catch {}
          setLoading(false);
          setReady("scenarios", true);
          // 새 시나리오 생성 완료 → 벨 알림 등록 (클릭 시 /scenarios 이동, 확인 시 꺼짐)
          // 수동 재생성마다 새 알림이 뜨도록 고유 id 사용 (notifyDone은 멱등이므로)
          notifyDone(`scenario-generate-${Date.now()}`, `시나리오 분석 완료 (${newIssues.length}건)`, "/scenarios");
        }
      } catch (e: any) {
        if (!cancelled) {
          if (e?.name === "AbortError") {
            setLoadError("AI 시나리오 분석 시간이 초과됐습니다 (3분). 잠시 후 다시 시도해주세요.");
          } else {
            setLoadError(String(e));
          }
          setLoading(false);
        }
      } finally {
        clearTimeout(timeoutId);
      }
    })();
    return () => { cancelled = true; controller.abort(); clearTimeout(timeoutId); };
  }, [fetchTrigger]);

  const handleUpdate = () => {
    setRegionFilter("전체");
    setFetchTrigger(n => (n ?? -1) + 1);
  };

  const handleCustomSearch = async (kw?: string) => {
    const keyword = (kw ?? customKeyword).trim();
    if (!keyword) return;
    setCustomLoading(true);
    setCustomError("");
    setShowRecent(false);

    // 최근 검색어 저장 (서버 + 화면 즉시 반영, 최대 10개)
    setRecentSearches(prev => [keyword, ...prev.filter(k => k !== keyword)].slice(0, 10));
    api.scenarios.saveRecent(keyword).catch(() => {});

    const newIdx = Math.min(customIssues.length, 9);
    try {
      const result = await readSSE(
        "/api/ai/scenarios/custom",
        "POST",
        { keyword },
        () => {}
      );
      // 빈/불완전 결과는 저장하지 않는다 (저장하면 이후 클릭 시 title undefined로 크래시)
      const r = result as Issue | null;
      if (!r || (!r.title && !(Array.isArray(r.scenarios) && r.scenarios.length > 0))) {
        throw new Error("분석 결과를 받지 못했습니다. 잠시 후 다시 시도해주세요.");
      }
      const searchedAt = new Date().toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
      // 서버에 저장하고 발급된 id를 받아 화면 상태에 반영 (삭제 시 사용)
      let newId: number | undefined;
      try {
        const saved = await api.scenarios.saveCustom(keyword, r.title || keyword, r, searchedAt);
        newId = saved?.id ?? undefined;
      } catch { /* 저장 실패해도 화면에는 표시 */ }
      const newIssue = { ...r, id: newId, title: r.title || keyword, isCustom: true as const, keyword, searchedAt };
      setCustomIssues(prev => [...prev, newIssue].slice(-10)); // FIFO max 10
      setRegionFilter("커스텀");
      setIssueIdx(newIdx);
      setCustomKeyword("");
    } catch (e) {
      setCustomError(cleanScenarioError(String(e)));
    } finally {
      setCustomLoading(false);
    }
  };

  const handleDeleteCustomIssue = (issue: Issue & { id?: number }) => {
    const idx = customIssues.findIndex(ci => ci === issue);
    setCustomIssues(prev => prev.filter(ci => ci !== issue));
    if (issue?.id != null) api.scenarios.deleteCustom(issue.id).catch(() => {});
    setIssueIdx(prev => (idx >= 0 && prev >= idx ? Math.max(0, prev - 1) : prev));
  };

  const filteredIssues: Array<Issue & { isCustom?: boolean; isAgent?: boolean }> = regionFilter === "에이전트"
    ? agentScenarios
    : regionFilter === "커스텀"
    ? customIssues
    : regionFilter === "전체"
      ? issues
      : issues.filter(issue => {
          const region = classifyIssueRegion(issue);
          if (regionFilter === "글로벌")    return region === "글로벌"  || region === "mixed";
          if (regionFilter === "국내")      return region === "국내"    || region === "mixed";
          if (regionFilter === "이머징마켓") return region === "이머징마켓";
          return true;
        });

  const clampedIdx  = issueIdx < filteredIssues.length ? issueIdx : 0;
  const activeIssue = filteredIssues[clampedIdx] ?? filteredIssues[0];

  if (!mounted) {
    return (
      <div style={{ width: "100%", padding: "2rem", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "300px", color: "var(--color-muted)" }}>
        <Loader2 className="animate-spin" size={24} style={{ marginBottom: "8px" }} />
        <span>화면을 준비하는 중입니다...</span>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", margin: "0 auto", display: "flex", flexDirection: "column", gap: "1rem" }}>

      {/* 헤더 */}
      <div style={{ borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "1rem", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 800, margin: "0 0 4px 0", display: "flex", alignItems: "center", gap: "8px" }}>
            <Globe color="var(--color-accent)" size={22} /> 매크로 시나리오 분석
          </h1>
          <div style={{ fontSize: "0.82rem", color: "var(--color-muted)" }}>
            글로벌 주요 이슈에 대한 A/B 시나리오와 투자 전략을 AI가 분석합니다.
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "4px" }}>
          {lastUpdated && !loading && (
            <div style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>마지막 업데이트: {lastUpdated}</div>
          )}
          {isAdmin ? (
            <button
              onClick={handleUpdate}
              disabled={loading}
              className="stockcy-btn stockcy-btn-primary"
              style={{ display: "flex", alignItems: "center", gap: "6px", padding: "6px 14px", fontSize: "0.82rem", fontWeight: 700, flexShrink: 0 }}
              title="AI 새로 분석 (약 1~2분)"
            >
              {loading ? <Loader2 className="animate-spin" size={15} /> : <RefreshCw size={15} />}
              {loading ? "분석 중..." : "AI 업데이트"}
            </button>
          ) : (
            <span style={{ fontSize: "0.72rem", color: "var(--color-muted)", padding: "6px 10px", border: "1px solid var(--color-border)", borderRadius: "6px", whiteSpace: "nowrap" }} title="시나리오는 관리자가 생성합니다">
              👁 읽기 전용
            </span>
          )}
        </div>
      </div>

      {/* 모바일 전용: 부가 정보(주요 지수·환율·시장경보·에이전트 이슈 등) 접기/펼치기 */}
      {isMobile && (
        <button
          onClick={() => setSidebarOpen(o => !o)}
          style={{
            display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%",
            padding: "10px 14px", borderRadius: "8px", cursor: "pointer",
            border: "1px solid var(--color-border)", background: "var(--color-card)",
            color: "var(--color-text)", fontSize: "0.85rem", fontWeight: 700,
          }}
        >
          <span>📊 주요 지수 · 환율 · 에이전트 이슈</span>
          {sidebarOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      )}

      {/* 2단 레이아웃 */}
      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: "1.5rem", alignItems: "start" }}>

        {/* ── 좌측: 시장 지표 ── (모바일에선 펼쳤을 때만 표시) */}
        {(!isMobile || sidebarOpen) && (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>

          <div className="stockcy-card" style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "10px" }}>
            <div style={{ fontSize: "0.82rem", fontWeight: 800, color: "var(--color-muted)", display: "flex", alignItems: "center", gap: "4px" }}>
              <TrendingUp size={13} /> 주요 지수 (미국)
            </div>
            {[
              { label: "S&P 500", key: "S&P 500" },
              { label: "NASDAQ",  key: "NASDAQ" },
              { label: "VIX",     key: "VIX" },
            ].map(({ label, key }) => {
              const d = (us as any)?.[key];
              const up = (d?.change_pct ?? 0) >= 0;
              return (
                <div key={key} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.04)", paddingBottom: "6px" }}>
                  <span style={{ fontSize: "0.8rem", fontWeight: 700 }}>{label}</span>
                  <span style={{ fontSize: "0.8rem", fontWeight: 800, color: key === "VIX" ? "var(--color-muted)" : up ? "var(--color-danger)" : "var(--color-primary)" }}>
                    {d ? `${d.price.toLocaleString()} (${d.change_pct >= 0 ? "+" : ""}${d.change_pct.toFixed(2)}%)` : "조회중"}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="stockcy-card" style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "10px" }}>
            <div style={{ fontSize: "0.82rem", fontWeight: 800, color: "var(--color-muted)", display: "flex", alignItems: "center", gap: "4px" }}>
              <DollarSign size={13} /> 환율 및 채권
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid rgba(255,255,255,0.04)", paddingBottom: "6px" }}>
              <span style={{ fontSize: "0.8rem", fontWeight: 700 }}>원/달러</span>
              <span style={{ fontSize: "0.8rem", fontWeight: 800, color: "var(--color-warning)" }}>
                {fxRate?.rate ? `₩${fxRate.rate.toLocaleString()}` : "—"}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontSize: "0.8rem", fontWeight: 700 }}>미 10년물</span>
              <span style={{ fontSize: "0.8rem", fontWeight: 800, color: "var(--color-primary)" }}>
                {tnx?.yield ? `${tnx.yield}%${tnx.change != null ? ` (${tnx.change >= 0 ? "+" : ""}${tnx.change})` : ""}` : "—"}
              </span>
            </div>
          </div>

          <div className="stockcy-card" style={{ padding: "12px", border: "1px solid var(--color-warning)", background: "rgba(255,180,50,0.05)" }}>
            <div style={{ fontSize: "0.8rem", fontWeight: 800, color: "var(--color-warning)", display: "flex", alignItems: "center", gap: "4px", marginBottom: "6px" }}>
              <AlertTriangle size={13} /> 시장 경보
            </div>
            <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", lineHeight: 1.5 }}>
              AI 분석 결과를 통해 확인하세요.
            </div>
          </div>

          {/* 커스텀 이슈 검색 */}
          <div className="stockcy-card" style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
            <div style={{ fontSize: "0.82rem", fontWeight: 800, color: "var(--color-muted)" }}>커스텀 이슈 검색</div>
            <div style={{ position: "relative" }}>
              <input
                className="stockcy-input"
                placeholder="키워드 (예: 반도체 관세)"
                value={customKeyword}
                onChange={e => setCustomKeyword(e.target.value)}
                onFocus={() => setShowRecent(true)}
                onBlur={() => setTimeout(() => setShowRecent(false), 150)}
                onKeyDown={e => e.key === "Enter" && handleCustomSearch()}
                style={{ fontSize: "0.82rem", width: "100%", boxSizing: "border-box" }}
              />
              {/* 최근 검색어 드롭다운 */}
              {showRecent && recentSearches.length > 0 && (
                <div style={{
                  position: "absolute", top: "100%", left: 0, right: 0, zIndex: 50,
                  background: "var(--color-card)", border: "1px solid var(--color-border)",
                  borderRadius: "6px", marginTop: "4px", overflow: "hidden",
                }}>
                  <div style={{ padding: "6px 10px", fontSize: "0.7rem", color: "var(--color-muted)", fontWeight: 700, borderBottom: "1px solid var(--color-border)" }}>
                    최근 검색어
                  </div>
                  {recentSearches.map((kw, i) => (
                    <div
                      key={i}
                      onMouseDown={() => { setCustomKeyword(kw); handleCustomSearch(kw); }}
                      style={{ padding: "6px 10px", fontSize: "0.8rem", cursor: "pointer", color: "var(--color-text)" }}
                      className="hover-highlight"
                    >
                      {kw}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <button
              className="stockcy-btn stockcy-btn-primary"
              onClick={() => handleCustomSearch()}
              disabled={customLoading || !customKeyword.trim()}
              style={{ width: "100%", padding: "8px", fontWeight: 700, fontSize: "0.82rem", display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}
            >
              {customLoading ? <><Loader2 className="animate-spin" size={14} /> 분석중...</> : "분석하기"}
            </button>
            {customError && <div style={{ fontSize: "0.75rem", color: "var(--color-danger)" }}>{customError}</div>}

            {/* 저장된 커스텀 이슈 목록 */}
            {customIssues.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "4px", marginTop: "4px" }}>
                <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", fontWeight: 700 }}>저장된 이슈 ({customIssues.length}/10)</div>
                {customIssues.map((issue, i) => (
                  <div
                    key={i}
                    style={{ display: "flex", alignItems: "center", gap: "4px" }}
                  >
                    <button
                      onClick={() => { setRegionFilter("커스텀"); setIssueIdx(i); }}
                      style={{
                        flex: 1, textAlign: "left", padding: "4px 8px", fontSize: "0.75rem",
                        borderRadius: "4px", border: "1px solid var(--color-border)",
                        background: "transparent", color: "var(--color-text)", cursor: "pointer",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}
                      title={issue.title}
                    >
                      <span>{issue.keyword || String(issue.title || "").slice(0, 16)}</span>
                      {(issue as any).searchedAt && (
                        <span style={{ fontSize: "0.65rem", color: "var(--color-muted)", display: "block", marginTop: "1px" }}>{(issue as any).searchedAt}</span>
                      )}
                    </button>
                    <button
                      onClick={() => handleDeleteCustomIssue(issue)}
                      style={{ flexShrink: 0, padding: "4px", background: "transparent", border: "none", cursor: "pointer", color: "var(--color-muted)" }}
                      title="삭제"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 에이전트 오늘의 이슈 */}
          <AgentDailyIssuesPanel />

          {/* 시나리오 적중률·추적은 '성과·기록' 페이지로 이동됨 */}
          <div style={{ fontSize: "0.78rem", color: "var(--color-muted)", textAlign: "center", padding: "10px", border: "1px dashed var(--color-border)", borderRadius: "8px" }}>
            📊 시나리오 적중률·추적 종목은 상단 <b>성과·기록</b> 탭에서 확인하세요.
          </div>

        </div>
        )}

        {/* ── 우측: 메인 콘텐츠 ── */}
        <div className="stockcy-card" style={{ padding: "1.5rem", minHeight: "500px" }}>

          {/* 탭: 시나리오 / 시장 인사이트 */}
          <div style={{ display: "flex", gap: "6px", marginBottom: "1.1rem" }}>
            {([["scenario", "🎯 시나리오"], ["insight", "📊 시장 인사이트"]] as const).map(([k, label]) => (
              <button key={k} onClick={() => setInsightTab(k)}
                style={{ padding: "7px 16px", fontSize: "0.85rem", fontWeight: 700, borderRadius: "8px", cursor: "pointer",
                  border: "1px solid " + (insightTab === k ? "var(--color-accent)" : "var(--color-border)"),
                  background: insightTab === k ? "rgba(99,102,241,0.15)" : "transparent",
                  color: insightTab === k ? "var(--color-text)" : "var(--color-muted)" }}>
                {label}{k === "scenario" && <span style={{ marginLeft: 5 }}><AiCostBadge small /></span>}
              </button>
            ))}
          </div>

          {/* 시장 인사이트 탭 — 이 탭을 열 때만 로드됨 (자동 호출 방지) */}
          {insightTab === "insight" && (
            <>
              <MarketCommentaryCard />
              <div style={{ marginBottom: "1.25rem" }}>
                <SupplyPowerFlow />
              </div>
              <div style={{ marginBottom: "1.25rem" }}>
                <SectorTrend />
              </div>
            </>
          )}

          {/* 새로고침 실패(예: 크레딧 없음)인데 이미 보던 시나리오가 있으면 → 본문은 유지하고 상단 알림 배너로만 표시 */}
          {insightTab === "scenario" && loadError && issues.length > 0 && (
            <div role="alert" style={{
              display: "flex", alignItems: "center", gap: "10px", padding: "10px 14px", marginBottom: "12px",
              borderRadius: "10px", border: "1px solid",
              borderColor: isCreditError(loadError) ? "rgba(251,191,36,0.5)" : "rgba(248,113,113,0.5)",
              background: isCreditError(loadError) ? "rgba(251,191,36,0.12)" : "rgba(248,113,113,0.12)",
              color: "var(--color-text)", fontSize: "0.85rem", fontWeight: 600,
            }}>
              <span style={{ fontSize: "1.05rem" }}>{isCreditError(loadError) ? "🔒" : "⚠️"}</span>
              <span style={{ flex: 1 }}>
                {cleanScenarioError(loadError)}
                <span style={{ color: "var(--color-muted)", fontWeight: 500 }}> · 아래는 관리자가 생성한 최신 시나리오입니다.</span>
              </span>
              <button onClick={() => setLoadError("")} title="닫기" style={{ background: "none", border: "none", color: "var(--color-muted)", cursor: "pointer", fontSize: "1rem", lineHeight: 1 }}>✕</button>
            </div>
          )}

          {insightTab === "scenario" && (loading ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "400px", gap: "1rem" }}>
              <Loader2 className="animate-spin" size={36} color="var(--color-accent)" />
              <div style={{ color: "var(--color-muted)", fontSize: "0.9rem", fontWeight: 600 }}>{statusMsg}</div>
            </div>
          ) : (loadError && issues.length === 0) ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "400px", gap: "0.8rem", textAlign: "center", padding: "2rem" }}>
              <div style={{ fontSize: "2.2rem" }}>{isCreditError(loadError) ? "🔒" : "⚠️"}</div>
              <div style={{ color: isCreditError(loadError) ? "var(--color-text)" : "var(--color-danger)", fontWeight: 700, fontSize: "0.95rem" }}>{cleanScenarioError(loadError)}</div>
              {isCreditError(loadError) && (
                <div style={{ fontSize: "0.82rem", color: "var(--color-muted)", lineHeight: 1.6 }}>관리자가 시나리오를 생성하면 여기에 읽기 전용으로 표시됩니다.</div>
              )}
            </div>
          ) : issues.length === 0 ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "400px", gap: "1rem" }}>
              <div style={{ fontSize: "2.5rem" }}>🤖</div>
              <div style={{ fontWeight: 700, fontSize: "1rem", color: "var(--color-text)" }}>AI 시나리오 분석이 필요합니다</div>
              {isAdmin ? (
                <>
                  <div style={{ fontSize: "0.85rem", color: "var(--color-muted)", textAlign: "center", lineHeight: 1.6 }}>
                    상단 <strong>AI 업데이트</strong> 버튼을 눌러 글로벌 시장 시나리오를 분석하세요.<br />
                    분석 결과는 모든 사용자에게 공유됩니다.
                  </div>
                  <button
                    onClick={handleUpdate}
                    className="stockcy-btn stockcy-btn-primary"
                    style={{ padding: "10px 24px", fontWeight: 700, fontSize: "0.9rem", display: "flex", alignItems: "center", gap: "8px" }}
                  >
                    <RefreshCw size={16} /> AI 시나리오 분석 시작
                  </button>
                </>
              ) : (
                <div style={{ fontSize: "0.85rem", color: "var(--color-muted)", textAlign: "center", lineHeight: 1.6 }}>
                  아직 생성된 시나리오가 없습니다.<br />관리자가 생성하면 여기에 표시됩니다. (읽기 전용)
                </div>
              )}
            </div>
          ) : (
            <>
              {/* 지역 필터 탭 */}
              <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", marginBottom: "12px" }}>
                {(["전체", "에이전트", "글로벌", "국내", "이머징마켓", "커스텀"] as RegionFilter[]).map(r => {
                  const labels: Record<RegionFilter, string> = {
                    "전체":      "전체",
                    "에이전트":  `🤖 에이전트${agentScenarios.length > 0 ? ` (${agentScenarios.length})` : ""}`,
                    "글로벌":    "🌍 글로벌 (미국)",
                    "국내":      "🇰🇷 국내",
                    "이머징마켓": "🌏 이머징마켓",
                    "커스텀":    `🔍 커스텀${customIssues.length > 0 ? ` (${customIssues.length})` : ""}`,
                  };
                  const active = regionFilter === r;
                  return (
                    <button
                      key={r}
                      onClick={() => { setRegionFilter(r); setIssueIdx(0); }}
                      style={{
                        padding: "5px 12px", fontSize: "0.78rem", fontWeight: 700, borderRadius: "6px",
                        border: "1px solid",
                        borderColor: active ? (r === "커스텀" ? "var(--color-warning)" : r === "에이전트" ? "#a5b4fc" : "var(--color-accent)") : "var(--color-border)",
                        background: active ? (r === "커스텀" ? "rgba(255,180,50,0.12)" : r === "에이전트" ? "rgba(99,102,241,0.15)" : "rgba(255,255,255,0.1)") : "transparent",
                        color: active ? (r === "커스텀" ? "var(--color-warning)" : r === "에이전트" ? "#a5b4fc" : "var(--color-text)") : "var(--color-muted)",
                        cursor: "pointer",
                        transition: "0.15s",
                      }}
                    >
                      {labels[r]}
                    </button>
                  );
                })}
              </div>

              {/* 커스텀 탭: 검색 UI */}
              {regionFilter === "커스텀" && (
                <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "12px", padding: "10px 12px", background: "rgba(255,180,50,0.06)", border: "1px solid rgba(255,180,50,0.2)", borderRadius: "8px" }}>
                  <input
                    className="stockcy-input"
                    placeholder="키워드 입력 (예: 반도체 관세, 금리 동결)"
                    value={customKeyword}
                    onChange={e => setCustomKeyword(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && handleCustomSearch()}
                    style={{ flex: 1, fontSize: "0.85rem" }}
                  />
                  <button
                    className="stockcy-btn stockcy-btn-primary"
                    onClick={() => handleCustomSearch()}
                    disabled={customLoading || !customKeyword.trim()}
                    style={{ padding: "8px 16px", fontWeight: 700, fontSize: "0.82rem", flexShrink: 0, display: "flex", alignItems: "center", gap: "6px" }}
                  >
                    {customLoading ? <><Loader2 className="animate-spin" size={14} /> 분석중...</> : "분석하기"}
                  </button>
                  {customError && <div style={{ fontSize: "0.75rem", color: "var(--color-danger)", flexShrink: 0 }}>{customError}</div>}
                </div>
              )}

              {/* 이슈 탭 */}
              {filteredIssues.length === 0 ? (
                <div style={{ color: "var(--color-muted)", fontSize: "0.85rem", padding: "2rem", textAlign: "center" }}>
                  {regionFilter === "커스텀"
                    ? "위 검색창에 키워드를 입력하고 분석하기를 눌러보세요."
                    : regionFilter === "에이전트"
                    ? "에이전트가 아직 오늘의 시나리오를 생성하지 않았습니다. 평일 아침 자동 생성되며, 좌측 '에이전트 오늘의 이슈'에서 갱신할 수 있습니다."
                    : "해당 지역의 이슈가 없습니다."
                  }
                </div>
              ) : (
                <>
                  <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginBottom: "1.25rem", borderBottom: "1px solid var(--color-border)", paddingBottom: "10px" }}>
                    {filteredIssues.map((issue, idx) => (
                      <div key={idx} style={{ display: "flex", alignItems: "center", gap: "2px" }}>
                        <button
                          onClick={() => setIssueIdx(idx)}
                          style={{
                            padding: "4px 12px", fontSize: "0.78rem", fontWeight: 600, borderRadius: "4px",
                            border: "1px solid",
                            borderColor: clampedIdx === idx ? "var(--color-accent)" : "var(--color-border)",
                            background: clampedIdx === idx ? "rgba(255,255,255,0.08)" : "transparent",
                            color: clampedIdx === idx ? "var(--color-text)" : "var(--color-muted)",
                            cursor: "pointer",
                            transition: "0.15s",
                          }}
                        >
                          {(issue as any).isCustom ? (
                            <span>
                              <span style={{ display: "block" }}>Custom {idx + 1}: {String((issue as any).keyword || issue.title || "").slice(0, 14)}{((issue as any).keyword || issue.title || "").length > 14 ? "…" : ""}</span>
                              {(issue as any).searchedAt && <span style={{ fontSize: "0.65rem", color: "var(--color-muted)", display: "block" }}>{(issue as any).searchedAt}</span>}
                            </span>
                          ) : (issue as any).isAgent ? (
                            <span>
                              <span style={{ display: "block" }}>🤖 {String(issue.title || (issue as any)._keyword || "").slice(0, 14)}{(issue.title || "").length > 14 ? "…" : ""}</span>
                              {(issue as any)._scenario_date && <span style={{ fontSize: "0.65rem", color: "var(--color-muted)", display: "block" }}>{(issue as any)._scenario_date}</span>}
                            </span>
                          ) : `Issue ${idx + 1}: ${String(issue.title || "").slice(0, 16)}${(issue.title || "").length > 16 ? "…" : ""}`}
                        </button>
                        {(issue as any).isCustom && (
                          <button
                            onClick={() => handleDeleteCustomIssue(issue as any)}
                            style={{ padding: "2px", background: "transparent", border: "none", cursor: "pointer", color: "var(--color-muted)", flexShrink: 0 }}
                            title="삭제"
                          >
                            <X size={11} />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>

                  {activeIssue && <IssuePanel key={`${regionFilter}-${clampedIdx}`} issue={activeIssue} />}
                </>
              )}
            </>
          ))}
        </div>
      </div>
    </div>
  );
}

const ScenariosPageContent = dynamic(() => Promise.resolve(ScenariosPageInner), {
  ssr: false,
  loading: () => (
    <div style={{ width: "100%", padding: "2rem", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "300px", color: "var(--color-muted)" }}>
      <Loader2 className="animate-spin" size={24} style={{ marginBottom: "8px" }} />
      <span>화면을 준비하는 중입니다...</span>
    </div>
  )
});

export default function ScenariosPage() {
  return <ScenariosPageContent />;
}
